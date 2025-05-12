#!/bin/env python3

import docker;
import re;
import subprocess;
import io, sys;

class Ichiran(object):

    simplelist = ['の','が','で','を', 'でも','僕'];
    noteregex = re.compile("^(?P<num>\d+)\. \[.*\] (?P<note>.*)$");
    conjregex = re.compile("\[ Conjugation: \[.*\] (Conjunctive|Continuative) \(.*\)\s?(?P<note>.*?)$");
    multiregex = re.compile("^.*<(?P<num>\d+)>. (?P<note>.*$)");

    

    def __init__(self, instance):
        self.instance = instance;


    def lookup(self, rawtext):
        rawtext = rawtext.replace('＊','');
        cmd = f'ichiran-cli -i "{rawtext}"';
        print(cmd);

        # docker mode
        if(self.instance):
            (ret, res) = self.instance.exec_run(cmd)
            if(ret):
                return None;
            return res.decode('utf8');
        # local mode
        else:
            cmd = ['ichiran-cli', '-i', rawtext];
            result = subprocess.run(cmd, capture_output=True, text=True);
            if(result.returncode):
                return None;
            return result.stdout;


    @staticmethod
    def parse_result(res, buffer=sys.stdout):
        buffer = io.StringIO();
        for segment in res.split('\n\n'):
            Ichiran.parse_segment(segment, buffer);
        return buffer.getvalue().rstrip("\n");

    @staticmethod
    def parse_segment(segment, buffer=sys.stdout):
        lines = segment.split("\n");
        #lines[0] = lines[0].split("  ")[1:]
        #if(lines[0] in Ichiran.simplelist):
        #    return;
        for line in lines:
            # remove additional junk per segment (first line)
            if(len(line) and line[0] == '*'):
                line = line.split('  ', 1)[1];
            if(len(line) > 2 and line[1] == '*'):
                print("", file=buffer);

            # parse multioptions
            m = re.match(Ichiran.multiregex, line)
            if(m):
                num = int(m.group('num'));
                if(num > 1):
                    print("", file=buffer);
                print(m.group('note'), end='', file=buffer);
                continue;

            # parse certain note notations
            m = re.match(Ichiran.noteregex, line)
            if(m):
                num = int(m.group('num'));
                if(num < 4):
                    print(" | " if num > 1 else " ", end='', file=buffer);
                    line = m.group('note');
                else:
                    break;

            # clean up conjugation info
            m = re.match(Ichiran.conjregex, line)
            if(m):
                if(m.group('note')):
                    print('  ' + m.group('note'), end='', file=buffer);
                continue;

            # remove trailing redundant ]
            line = line.replace(']', '');
            print(line, end='', file=buffer);

            # skip explains on simple stuff
            if(line in Ichiran.simplelist):
                break;
        print("", file=buffer);


def get_ichiran():
    # for docker
    #client = docker.from_env();
    #ichiran = client.containers.get('ichiran_main_1')
    #return Ichiran(ichiran);
    # for local
    return Ichiran(None);

def main_test():
    ichiran = get_ichiran()
    a = "母親";

    res = ichiran.lookup(a);
    res = ichiran.parse_result(res);
    print(res);


if(__name__ == "__main__"):
    main_test();
