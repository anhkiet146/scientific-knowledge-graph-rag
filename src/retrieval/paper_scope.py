import re
import unicodedata
from collections import defaultdict

STOP=set('a an the and or of on in to for from with by is are was were this that these those study studies research paper papers method methods analysis analytical chemical structure structures compounds compound used using determine identify identification isolation isolated effects effect evaluation evaluating comparison application applications results properties synthesis phuong phap phan tich nao duoc dung de xac dinh cau truc hoa hoc cac hop chat tu loai nghien cuu bai bao nhung gi cua ve tren voi va'.split())


def words(text):
    return re.findall(r'\w+',unicodedata.normalize('NFKC',text).casefold())


class PaperScope:
    def __init__(self,titles,max_frequency=3,max_papers=8,entity_names=None):
        self.max_frequency=max_frequency;self.max_papers=max_papers
        self.entity_phrases=set()
        for name in entity_names or []:
            values=[name]
            if re.search(r'\([A-Za-z][A-Za-z0-9-]*\)\s*$',name):values.append(name.split('(')[0].strip())
            for value in values:
                phrase=' '.join(words(value))
                if len(phrase)>=4:self.entity_phrases.add(phrase)
        self.single=defaultdict(set);self.pairs=defaultdict(set)
        for paper,title in titles.items():
            tokens=words(title)
            for token in set(tokens):self.single[token].add(paper)
            for pair in set(zip(tokens,tokens[1:])):self.pairs[pair].add(paper)

    def select(self,query,named_entities=None):
        tokens=words(query);anchors={}
        named_tokens={name_tokens[0] for name in (named_entities or []) if len(name_tokens:=words(name))==1}
        query_phrase=' '+' '.join(tokens)+' '
        for phrase in self.entity_phrases:
            if ' ' not in phrase and ' '+phrase+' ' in query_phrase:named_tokens.add(phrase)
        for token in tokens:
            if token in STOP or token.isnumeric():continue
            informative=len(token)>=8 or (len(token)>=3 and any(c.isalpha() for c in token) and any(c.isdigit() for c in token))
            matches=self.single.get(token,set())
            if informative and 0<len(matches)<=self.max_frequency:anchors[token]=matches
        for pair in zip(tokens,tokens[1:]):
            matches=self.pairs.get(pair,set())
            if all(len(t)>=3 and t not in STOP for t in pair) and 0<len(matches)<=self.max_frequency:anchors[' '.join(pair)]=matches
        support=defaultdict(set);strong=set()
        for anchor,matches in anchors.items():
            for paper in matches:support[paper].add(anchor)
            if ' ' in anchor or (any(c.isdigit() for c in anchor) and any(c.isalpha() for c in anchor)) or (anchor in named_tokens and len(anchor)>=4 and len(matches)==1):strong.update(matches)
        papers=strong|{paper for paper,terms in support.items() if len(terms)>=2}
        active=bool(papers) and len(papers)<=self.max_papers
        return {'state':'scoped' if active else 'no_specific_title_anchor' if not papers else 'too_many_matching_papers',
                'allowed_papers':sorted(papers) if active else None,
                'anchors':{key:sorted(value) for key,value in sorted(anchors.items())},
                'limits':'Experimental lexical title scope, not a relevance label; metadata misses and title collisions remain possible.'}


class ScopedIndex:
    def __init__(self,index,keys,groups,papers):
        self.index=index;self.keys=keys;self.groups=groups;self.papers=set(papers)

    def search(self,query,k):
        candidates=self.index.search(query,len(self.keys))
        return [(i,score) for i,score in candidates if any(o['paper'] in self.papers for o in self.groups[self.keys[i]])][:k]
