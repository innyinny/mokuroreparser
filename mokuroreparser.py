#!/bin/env python3

import os;
import argparse;
import json;
import pyperclip;
from ichiran_parser import get_ichiran;

from transformers import MarianMTModel, MarianTokenizer;
from typing import Sequence;

class Translator:
    def __init__(self, source_lang: str, dest_lang: str) -> None:
        self.model_name = f'Helsinki-NLP/opus-mt-{source_lang}-{dest_lang}'
        self.model = MarianMTModel.from_pretrained(self.model_name)
        self.tokenizer = MarianTokenizer.from_pretrained(self.model_name)

    def translate(self, texts: Sequence[str]) -> Sequence[str]:
        tokens = self.tokenizer(list(texts), return_tensors="pt", padding=True)
        translate_tokens = self.model.generate(**tokens, max_new_tokens=200)
        return [self.tokenizer.decode(t, skip_special_tokens=True) for t in translate_tokens]


# parse the arguments
argparser = argparse.ArgumentParser();
argparser.add_argument("input");
argparser.add_argument("-y", "--overwrite", dest="overwrite", action='store_true', default=None,
                       help="overwrite outfile if it exists");
argparser.add_argument("-m", "--manual", dest="manual", action='store_true', default=False,
                       help="allow manual translation entry");
argparser.add_argument("-o", "--offline", dest="offline", action='store_true', default=False,
                       help="run auto offline translation (MarianMT)");
argparser.add_argument("-g", "--glossary", dest="glossary", action='store_true', default=False,
                       help="run glossary lookup (docker ichiran)");
argparser.add_argument("-f", "--font", dest="font", default="victory/18",
                       help="the default font to use");


args = argparser.parse_args();

mariantrans = None;
ichiran = None;


# goes through all of the image files in the directory
def iterate_directory(input):
    print(input);
    dirlist = None;
    if(os.path.isfile(input)):
        dirlist = [input];
    else:
        dirlist = os.listdir(input);
    
    print(len(dirlist))
    n = 0;

    for entry in sorted(dirlist):
        # tmp junk
        #n += 1;
        #if(n == 1):
        #    continue;
        #if(n > 2):
        #    break;
        ###

        # make sure its an image
        if('.' in entry and entry.split('.')[-1] in ('jpg','png','gif','JPG','PNG')):
            process_file(entry);


# handles everything related to the image file (its captions and json files)
def process_file(entry):
    global args;
    fullpath = os.path.abspath(entry);
    print(fullpath);

    # gather path parts
    pathparts = fullpath.split('/');
    pathparts[-1] = pathparts[-1].split('.')[0];

    # json path
    jsonpath = "/".join(pathparts[:-2] + ['_ocr'] + pathparts[-2:]) + ".json";
    if(not os.path.isfile(jsonpath)):
        jsonpath = "/".join(pathparts[:-1] + ['_ocr'] + pathparts[-1:]) + ".json";

    # caption path
    captpath = "/".join(pathparts[:-1] + ['captions'] + pathparts[-1:]) + ".txt";

    # caption dir
    captdir = "/".join(pathparts[:-1] + ['captions']);

    # check if caption dir exists
    if(not os.path.exists(captdir)):
        os.makedirs(captdir)

    # check if caption file exists
    if(not args.overwrite and os.path.isfile(captpath)):
        print("File %s already exists, use -y to overwrite?" % captpath);
        return;

    # get the data from the mokuro json file
    try:
        blocks = process_file_json(jsonpath);
    except FileNotFoundError as e:
        return;
    if(args.manual):
        blocks = step_translate_blocks(blocks);
    elif(args.offline):
        blocks = auto_translate_blocks(blocks);
    if(args.glossary):
        blocks = glossary_lookup_blocks(blocks);

    write_caption_file(captpath, blocks);


#handles open the json file and returning the blocks from the buffer
def process_file_json(jsonpath):
    with open(jsonpath) as inf:
        j = json.load(inf);
    blocks = j['blocks'];

    for b in blocks:
        rawtext = "".join(b['lines']);
        b['rawtext'] = rawtext;

    return blocks;


# steps through the lines in a block allowing manual entry
def step_translate_blocks(blocks):
    global mariantrans;
    if(not mariantrans):
        mariantrans = Translator('ja','en');

    translated_blocks = [];

    while(len(blocks)):
        b = blocks[0];

        pyperclip.copy(b['rawtext']);
        print("Raw:  " + b['rawtext']);

        # pass the translations to the offline engine
        #if('autotrans' not in b):
        #    offlinetranslation = trans_filter(mariantrans.translate([b['rawtext']])[0]);

        #print('Auto: ' + b['autotrans']);
        
        # take the translation from prompt
        try:
            
            print("Enter the translation...");
            entered = input("");
            if(entered == ""):
                #skip
                b = blocks.pop(0);
                blocks.append(b);
                print("skipped");
                continue;

            b['trans'] = input("");
            translated_blocks.append(blocks.pop(0));
        except EOFError:
            blocks.pop(0);
            print("removed");

    return translated_blocks;


# just auto translate the blocks
def auto_translate_blocks(blocks):
    if(len(blocks) < 1):
        return blocks;

    global mariantrans;
    if(not mariantrans):
        mariantrans = Translator('ja','en');

    pagelines = [b['rawtext'] for b in blocks];
    print("\n".join(pagelines));
    offlinetranslation = mariantrans.translate(pagelines);
    
    # merge the results with the blocks
    for i in range(len(offlinetranslation)):
        offlinetranslation[i] = trans_filter(offlinetranslation[i]);
        if(offlinetranslation[i]):
            blocks[i]['autotrans'] = offlinetranslation[i];
            print(offlinetranslation[i]);

    return blocks;


# glossary lookup on the blocks
def glossary_lookup_blocks(blocks):
    global ichiran;
    if(len(blocks) < 1 or not ichiran):
        return blocks;

    # process blocks one by one
    for block in blocks:
        print(block['rawtext']);
        glostext = [];
        for sentence in block['rawtext'].split('。'):
            if(not sentence):
                continue;
            res = ichiran.lookup(sentence);

            if(not res):
                print("ichiran lookup failed");
                return blocks;

            res = ichiran.parse_result(res).split("\n");
            if(len(glostext)):
                glostext.append("");
            glostext += res;

        block['glossary'] = glostext;

    return blocks;


# writes all the block data to the caption file
def write_caption_file(captpath, blocks):

    # try to open the caption file
    try:
        outf = open(captpath, 'w' if args.overwrite else 'x');
    except FileExistsError as e:
        print("File %s already exists, use -y to overwrite?" % captpath);
        return;

    print("#centered", file=outf);

    # print everything out to file and screen
    for b in blocks:
        print('', file=outf);
        (x1, y1, x2, y2) = b['box'];
        print("#%u,%u" % (x1 + (x2 - x1)/2, y1 + (y2 - y1)/2), file=outf);
        #print("#font:victory/%u" % (b['font_size'] / 3), file=outf);
        print("#font:%s" % args.font, file=outf);
        if('autotrans' in b and len(b['autotrans'])):
            print('#' + b['autotrans'], file=outf);
        if('glossary' in b and len(b['glossary'])):
            for fragment in b['glossary']:
                print('# ' + fragment, file=outf);
        print(b['rawtext'].replace('。', "。\n"), file=outf);
        if('trans' in b and len(b['trans'])):
            print(b['trans'], file=outf);
        print('', file=outf);

    outf.close();


# filter the auto translations idiotic mistranslations
def trans_filter(trans):
    if(len(trans) > 50 and
    (
        #len(list(set([b.strip(' ,.!') for b in trans.lower().split(' ')]))) < 6 or
        len(list(set([b.strip(' ,.!') for b in trans.lower().split(',')]))) < 6
    )):
        return None;
    return trans;        


#### main
# init glossary
if(args.glossary):
    ichiran = get_ichiran();

iterate_directory(args.input);
