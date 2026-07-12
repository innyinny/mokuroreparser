#!/bin/env python3

import os;
import argparse;
import json;
import pyperclip;
import textwrap;
from collections import deque;

from ichiran_parser import get_ichiran;

from typing import Sequence;

from openai import OpenAI;

strictprompt = """You are a literal Japanese-to-English translation engine. Your goal is structural fidelity, not natural English flow.
Strict Constraints:
- PRESERVE ALL NOUNS: Never omit or replace specific nouns (e.g., 母さん，父，先生) with pronouns. If the source says "Mother," you must output "Mother" or "Mom," never "she" or "her." If the noun is repeated in Japanese, repeat it in English.
- NO ADDED PRONOUNS: Do not add English pronouns (he, she, they, it) unless a specific pronoun (kare, kanojo, watashi, etc.) exists in the source text. If the subject is omitted in Japanese, leave it omitted in English or use the previous noun.
- GENDER-NEUTRAL TRANSLATION: Translate ambiguous terms like おやこ (oyako) strictly as "parent and child" or "parent-child." Never assume gender. If a pronoun is grammatically unavoidable and no gender is specified, use "they/them" or passive voice.
- HONORIFICS & TONE: Retain the nuance of honorifics (e.g., translate 母さん as "Mom" or "Mother" depending on context, not just "parent") but do not add gendered assumptions to them.
- NO SMOOTHING: Do not rephrase sentences to sound more "natural" if it requires adding words not present in the source.
Output ONLY the translation."""

lightprompt = """You are a professional localizer whose primary goal is to translate Japanese to English. You should use colloquial or slang or nsfw vocabulary if it makes the translation more accurate. Always respond in English."""

mediumprompt = """You are a literal Japanese to English localizer.
Rules:
- Use colloquial or slang or nsfw vocabulary if it makes the translation more accurate. 
- Preserve original nouns and pronouns. Don't replace, add extra, or add gender to pronouns.
- Always respond in English."""

sugoi32b = 'sugoi-32b-ultra';
sugoi14b = 'sugoi-14b-ultra-hf-i1';

class OpenAITranslator:
    def __init__(self) -> None:
        self.model_name = 'sugoi32b';
        self.client = OpenAI(base_url='http://localhost:1234/v1', api_key='not-needed');
        self.context = deque(maxlen=8);
        self.alreadytranslated = {};
        self.system_instruction = strictprompt;


    def translate(self, texts: Sequence[str]) -> Sequence[str]:
        results = [];
        for text in texts:
            alreadytranslated = self.alreadytranslated.get(text, None);
            if(alreadytranslated):
                results.append(alreadytranslated);
                continue;
            self.context.append({"role": "user", "content": text});
            result = self.client.chat.completions.create(
                model=self.model_name,
                temperature = 0.1,
                messages= [{"role":"system", "content":self.system_instruction}] + list(self.context),
            ).choices[0].message.content.strip();
            self.alreadytranslated[text] = result;
            results.append(result);
            self.context.append({"role": "assistant", "content": result});
        return results;


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

translator = None;
ichiran = None;


# initializes the translator
def init_translator():
    global translator;
    if(not translator):
        translator = OpenAITranslator();
    return translator;


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
    translated_blocks = [];

    while(len(blocks)):
        b = blocks[0];

        pyperclip.copy(b['rawtext']);
        print("Raw:  " + b['rawtext']);

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
    global translator;

    if(len(blocks) < 1):
        return blocks;

    translator = init_translator();

    pagelines = [b['rawtext'] for b in blocks];
    print("\n".join(pagelines));
    offlinetranslation = translator.translate(pagelines);
    print(offlinetranslation);
    
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
        if('glossary' in b and len(b['glossary'])):
            for fragment in b['glossary']:
                print('# ' + fragment, file=outf);
        print(b['rawtext'].replace('。', "。\n"), file=outf);
        if('trans' in b and len(b['trans'])):
            displayedtrans = b['trans'];
            print('#' + b['trans'], file=outf);
        if('autotrans' in b and len(b['autotrans'])):
            displayedtrans = b['autotrans'];
            print('#' + b['autotrans'], file=outf);
        #if('autotrans' in b and len(b['autotrans'])):
        #    #for tline in b['autotrans'].rstrip('.').split(' '):
        #    #    print(tline, file=outf);
        #elif('trans' in b and len(b['trans'])):
        #    #for tline in b['trans'].rstrip('.').split(' '):
        #    #    print(tline, file=outf);
        if(displayedtrans):
            for tline in list(
                textwrap.wrap(displayedtrans,
                    width=int((x2 - x1) / 9) or 10,
                    break_long_words=False)
                ):
                print(tline, file=outf);
        print('', file=outf);

    outf.close();


def trans_filter(trans):
    # filter the auto translations idiotic mistranslations (not needed anymore?)
    #if(len(trans) > 50 and
    #(
    #    #len(list(set([b.strip(' ,.!') for b in trans.lower().split(' ')]))) < 6 or
    #    len(list(set([b.strip(' ,.!') for b in trans.lower().split(',')]))) < 6
    #)):
    #    return None;
    
    #do simple character replacements for viewer compatibility
    return trans.replace('♥', '@');


#### main
# init glossary
if(args.glossary):
    ichiran = get_ichiran();

iterate_directory(args.input);
