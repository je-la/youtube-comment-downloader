#!/usr/bin/env python

from __future__ import print_function

import argparse
import io
import json
import os
import sys
import time

import re
import requests

YOUTUBE_VIDEO_URL = 'https://www.youtube.com/watch?v={youtube_id}'

USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.130 Safari/537.36'

SORT_BY_POPULAR = 0
SORT_BY_RECENT = 1

YT_CFG_RE = r'ytcfg\.set\s*\(\s*({.+?})\s*\)\s*;'
YT_INITIAL_DATA_RE = r'(?:window\s*\[\s*["\']ytInitialData["\']\s*\]|ytInitialData)\s*=\s*({.+?})\s*;\s*(?:var\s+meta|</script|\n)'


def regex_search(text, pattern, group=1, default=None):
    match = re.search(pattern, text)
    return match.group(group) if match else default


def isCommentAReply(comment):
    return '.' in comment['commentId']


def comment_dict(comment):
    return {'cid': comment['commentId'],
           'text': ''.join([c['text'] for c in comment['contentText'].get('runs', [])]),
           'time': comment['publishedTimeText']['runs'][0]['text'],
           'author': comment.get('authorText', {}).get('simpleText', ''),
           'channel': comment['authorEndpoint']['browseEndpoint'].get('browseId', ''),
           'votes': comment.get('voteCount', {}).get('simpleText', '0'),
           'photo': comment['authorThumbnail']['thumbnails'][-1]['url'],
           'heart': next(search_dict(comment, 'isHearted'), False)}

def output_comments(cached_comments_list, cached_replies_dict):
    for comment in cached_comments_list:
        cid = comment['commentId']              
        yield comment_dict(comment)                                           
        for reply in cached_replies_dict[cid]:
            yield comment_dict(reply) 
    

               
def ajax_request(session, endpoint, ytcfg, retries=5, sleep=20):
    url = 'https://www.youtube.com' + endpoint['commandMetadata']['webCommandMetadata']['apiUrl']
    
    data = {'context': ytcfg['INNERTUBE_CONTEXT'],
            'continuation': endpoint['continuationCommand']['token']}

    for _ in range(retries):
        response = session.post(url, params={'key': ytcfg['INNERTUBE_API_KEY']}, json=data)
        if response.status_code == 200:
            return response.json()
        if response.status_code in [403, 413]:
            return {}
        else:
            time.sleep(sleep)


def download_comments(youtube_id, fp, sort_by=SORT_BY_RECENT, sleep=.1):
    
    fp1 = io.open('data', 'w', encoding='utf8')
        
    session = requests.Session()
    session.headers['User-Agent'] = USER_AGENT

    response = session.get(YOUTUBE_VIDEO_URL.format(youtube_id=youtube_id))

    if 'uxe=' in response.request.url:
        session.cookies.set('CONSENT', 'YES+cb', domain='.youtube.com')
        response = session.get(YOUTUBE_VIDEO_URL.format(youtube_id=youtube_id))

    html = response.text
    ytcfg = json.loads(regex_search(html, YT_CFG_RE, default=''))
    if not ytcfg:
        return  # Unable to extract configuration

    data = json.loads(regex_search(html, YT_INITIAL_DATA_RE, default=''))

    section = next(search_dict(data, 'itemSectionRenderer'), None)
    
    renderer = next(search_dict(section, 'continuationItemRenderer'), None) if section else None
    
    if not renderer:
        # Comments disabled?
        return

    needs_sorting = sort_by != SORT_BY_POPULAR
    continuations = [renderer['continuationEndpoint']]
    
    cached_comments_list = []
    cached_replies_dict = {}
    
    while continuations:
        continuation = continuations.pop()
        
        # print("****** ", file=fp)        
        # print("*** " + str(len(continuations)) + " ***", file=fp)
        # print("******", file=fp)  
        
        continuations_stack_empty = len(continuations) == 0
        
        response = ajax_request(session, continuation, ytcfg)

        if not response:
            break
        
        # print(str(response), file=fp1 )
        # fp1.flush()
        
        if list(search_dict(response, 'externalErrorMessage')):
            raise RuntimeError('Error returned from server: ' + next(search_dict(response, 'externalErrorMessage')))

        if needs_sorting:
            sort_menu = next(search_dict(response, 'sortFilterSubMenuRenderer'), {}).get('subMenuItems', [])
            if sort_by < len(sort_menu):
                continuations = [sort_menu[sort_by]['serviceEndpoint']]
                needs_sorting = False
                continue
            raise RuntimeError('Failed to set sorting')

        actions = list(search_dict(response, 'reloadContinuationItemsCommand')) + \
                  list(search_dict(response, 'appendContinuationItemsAction'))
        for action in actions:
            for item in action.get('continuationItems', []):
                if action['targetId'] == 'comments-section':
                    # Process continuations for comments and replies.
                    continuations[:0] = [ep for ep in search_dict(item, 'continuationEndpoint')]
                if action['targetId'].startswith('comment-replies-item') and 'continuationItemRenderer' in item:
                    # Process the 'Show more replies' button
                    continuations.append(next(search_dict(item, 'buttonRenderer'))['command'])
        
        
        
        comment_list = list(reversed(list(search_dict(response, 'commentRenderer'))))
        
        if len(comment_list) > 0:
            if continuations_stack_empty and not isCommentAReply(comment_list[0]):
                
                # a new comments-replies-bunch starts
                
                # output cached comments and replies in youtube-order:
                for comment in output_comments(cached_comments_list, cached_replies_dict):
                    yield comment                        
                
                # reset caches
                cached_comments_list = []
                cached_replies_dict = {}   
                                     
                # cache up comments ...
                for comment in comment_list:
                    cached_replies_dict[comment['commentId']] = []
                    cached_comments_list.append(comment)
                
            else:
                # cache up replies ...
                cid = comment_list[0]['commentId'].split('.')[0]
                for comment in comment_list:
                     cached_replies_dict[cid].append(comment)                                          
                                   

     
        time.sleep(sleep)
    
    # output remaining cached comments and replies in youtube-order:
    for comment in output_comments(cached_comments_list, cached_replies_dict):
        yield comment

    fp1.close()


def search_dict(partial, search_key):
    stack = [partial]
    while stack:
        current_item = stack.pop()
        if isinstance(current_item, dict):
            for key, value in current_item.items():
                if key == search_key:
                    yield value
                else:
                    stack.append(value)
        elif isinstance(current_item, list):
            for value in current_item:
                stack.append(value)


def main(argv=None):
    parser = argparse.ArgumentParser(add_help=False, description=('Download Youtube comments without using the Youtube API'))
    parser.add_argument('--help', '-h', action='help', default=argparse.SUPPRESS, help='Show this help message and exit')
    parser.add_argument('--youtubeid', '-y', help='ID of Youtube video for which to download the comments')
    parser.add_argument('--output', '-o', help='Output filename (output format is line delimited JSON)')
    parser.add_argument('--limit', '-l', type=int, help='Limit the number of comments')
    parser.add_argument('--sort', '-s', type=int, default=SORT_BY_RECENT,
                        help='Whether to download popular (0) or recent comments (1). Defaults to 1')

    try:
        args = parser.parse_args() if argv is None else parser.parse_args(argv)

        youtube_id = args.youtubeid
        output = args.output
        limit = args.limit

        if not youtube_id or not output:
            parser.print_usage()
            raise ValueError('you need to specify a Youtube ID and an output filename')

        if os.sep in output:
            outdir = os.path.dirname(output)
            if not os.path.exists(outdir):
                os.makedirs(outdir)

        print('Downloading Youtube comments for video:', youtube_id)
        count = 0
        with io.open(output, 'w', encoding='utf8') as fp:
            sys.stdout.write('Downloaded %d comment(s)\r' % count)
            sys.stdout.flush()
            start_time = time.time()            
            first = True            
            for comment in download_comments(youtube_id, fp, args.sort):
                comment_json = json.dumps(comment, ensure_ascii=False)
                
                # regular json output                               
                if not first:
                    print(','.decode('utf-8'), file=fp)
                else:       
                    first = False
                
                print(comment_json.decode('utf-8') if isinstance(comment_json, bytes) else comment_json, file=fp)
                               
                count += 1
                sys.stdout.write('Downloaded %d comment(s)\r' % count)
                sys.stdout.flush()
                if limit and count >= limit:
                    break
        print('\n[{:.2f} seconds] Done!'.format(time.time() - start_time))

    except Exception as e:
        print('Error:', str(e))
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
