"""Versioned extraction relations; experimental changes never alter legacy data."""
import copy

LEGACY='legacy-v3.1'
COMPOSITION='composition-experimental-v1'
ENTITY_TYPES=['Concept','Method','Dataset','Metric','Domain','Author','Institution']
BASE_SIGNATURES={'BELONGS_TO':('Concept','Domain'),'USED_FOR':('Method','Concept'),
    'EVALUATED_ON':('Method','Dataset'),'ACHIEVED':('Method','Metric'),
    'AFFILIATED_WITH':('Author','Institution')}


def signatures(profile=LEGACY):
    if profile not in (LEGACY,COMPOSITION):raise ValueError('Unknown ontology profile')
    result=dict(BASE_SIGNATURES)
    if profile==COMPOSITION:result['HAS_COMPONENT']=('Method','Method')
    return result


def schema_for_profile(schema,profile=LEGACY):
    result=copy.deepcopy(schema)
    result['properties']['relations']['items']['properties']['type']['enum']=list(signatures(profile))
    return result


def relation_instructions(profile=LEGACY):
    rules=signatures(profile)
    text='Only these directed relations are allowed:\n'
    text+='; '.join(f'{a} {kind} {b}' for kind,(a,b) in rules.items())+'.\n'
    if profile==COMPOSITION:
        text+=('HAS_COMPONENT means the source method explicitly incorporates the target method as an operational component. '
               'Co-mention, comparison, citation, chronological succession or shared application is insufficient. '
               'Never emit a self-component edge or rename USED_FOR to HAS_COMPONENT without source support.\n')
    return text
