#!/usr/bin/python3

'''
Created on 08.08.2021

@author: je-la
'''

import sys
import time
import json
import argparse
import io
import fileinput

#
#  simple script to convert json-data obtained from youtube_comment_downloader.py 
#  to 'pretty' text-output 
# 


def isCommentAReply(comment):
    return '.' in comment['cid']


def main(argv=None):
    
    t = int (1e6 * time.time())
    default_output_file = "youtube_comments_" + str(t) + ".txt" 
        
    parser = argparse.ArgumentParser(add_help=False, description=('Convert json-data obtained from youtube_comment_downloader.py to \'pretty\' text-output'))
    parser.add_argument('--help', '-h', action='help', default=argparse.SUPPRESS, help='Show this help message and exit')
    parser.add_argument('--outputfile', '-o', default=default_output_file, help='name of the output-file (Default: youtube_comments_<timecode>.txt)')
    parser.add_argument('inputfile', help='name of the input-file')
    
    args = parser.parse_args() if argv is None else parser.parse_args(argv)
    input_file = args.inputfile
    output_file = args.outputfile
      
    # assuming one line in input-file represents one comment-object ...  
      
    with io.open(output_file, 'w', encoding='utf8') as fp_o, fileinput.input(files=(input_file)) as fp_i:
        for line in fp_i:            
            comment = json.loads(line) 
            if isCommentAReply(comment):
                print('\t' + comment['author'], file=fp_o)
                print('\t' + comment['time'], file=fp_o)
                print('\t' + comment['text'], file=fp_o)
            else:
                print(comment['author'], file=fp_o)
                print(comment['time'], file=fp_o)
                print(comment['text'], file=fp_o) 
                        
            print('\n', file=fp_o)
                
                      
    print("bye.")
    
if __name__ == "__main__":
    main(sys.argv[1:])
    
