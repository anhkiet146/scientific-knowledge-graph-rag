"""Canonical whole-record context packing; never truncate a scientific claim."""
import json


def pack(records,encode,limit=2000):
    if type(limit) is not int or limit<1:raise ValueError('Positive token budget required')
    selected=[]
    for record in records:
        candidate=selected+[record]
        text=json.dumps(candidate,ensure_ascii=False,sort_keys=True,separators=(',',':'))
        if len(encode(text))>limit:break
        selected=candidate
    text=json.dumps(selected,ensure_ascii=False,sort_keys=True,separators=(',',':'))
    count=len(encode(text))
    if count>limit:raise ValueError('Empty context cannot fit token budget')
    return selected,text,count


def pack_v2(records,encode,limit=2000):
    """Stable greedy whole-record selection, continuing after a non-fitting item.

    Never shrink evidence, invent sources or use an answer key. The manifest must
    distinguish this policy from historical prefix packing. Return an audit for
    every exclusion; do not present these as measured recall or QA improvements.
    """
    if type(limit) is not int or limit<1:raise ValueError('Positive token budget required')
    def serialize(items):return json.dumps(items,ensure_ascii=False,sort_keys=True,separators=(',',':'))
    if len(encode(serialize([])))>limit:raise ValueError('Empty context cannot fit token budget')
    selected=[];audit=[]
    for index,record in enumerate(records):
        candidate=selected+[record];count=len(encode(serialize(candidate)))
        accepted=count<=limit
        audit.append({'rank':index,'accepted':accepted,'candidate_tokens':count,
                      'reason':'included' if accepted else 'whole_record_over_budget'})
        if accepted:selected=candidate
    text=serialize(selected)
    return selected,text,len(encode(text)),audit


def evidence_units(ranked):
    """Round-robin full source occurrences across ranked nodes, then relations.

    No flattening of descriptions across papers. Stable source order; duplicate
    occurrences appear once. Nodes without preservation metadata are rejected.
    This is a new, declared evidence representation, not a historical replay.
    """
    entities=[];relations=[]
    for node in ranked:
        if 'evidence_occurrences' not in node:raise ValueError('Preserved source occurrences required')
        entities.append(node['evidence_occurrences']);relations.append(node.get('relation_occurrences',[]))
    result=[];seen=set()
    for groups in (entities,relations):
        for offset in range(max((len(g) for g in groups),default=0)):
            for group in groups:
                if offset>=len(group):continue
                record=group[offset];identity=json.dumps(record,ensure_ascii=False,sort_keys=True)
                if identity in seen:continue
                seen.add(identity);result.append(record)
    return result
