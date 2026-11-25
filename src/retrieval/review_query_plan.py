import re
from hybrid_retrieval import build_query_plan,normalize_text


def build_plan(query):
    plan=build_query_plan(query,{'keywords':[query]})
    glosses={normalize_text(s) for s in re.findall(r'\(([^()]{2,120})\)',query) if len(s.split())>1}
    explicit={normalize_text(s) for s in plan.get('required_entities',[])}
    demoted=glosses-explicit
    plan['entities']=[s for s in plan.get('entities',[]) if normalize_text(s) not in demoted]
    plan['subject_terms']=[s for s in plan.get('subject_terms',[]) if normalize_text(s) not in demoted]
    for s in sorted(demoted):
        if s not in plan['search_terms']:plan['search_terms'].append(s)
    normalized=normalize_text(query)
    if plan['answer_type']=='entity':
        if any(term in normalized for term in ('dinh nghia','definition','defined in','defined as','what is meant by')):
            plan['expected_labels']=['concept','method'];plan['retrieval_intent']='definition_evidence'
        elif re.search(r'\b(sort|sorting|sorted)\b|sap xep',normalized):
            plan['expected_labels']=['concept','method'];plan['retrieval_intent']='sorting_rule_evidence'
        elif re.search(r'\b(which|what)\s+(?:new\s+)?compounds\b|hop chat.*\bnao\b',normalized):
            plan['expected_labels']=['concept','metric'];plan['retrieval_intent']='compound_list_evidence'
    plan['parsing_policy']='review-v1-soft-multiword-parentheses'
    plan['soft_parenthetical_terms']=sorted(demoted)
    return plan
