import os
import re


def selected_database():
    value=os.getenv('NEO4J_DATABASE')
    if value is None:return None
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]{0,62}',value) or value.casefold()=='system':
        raise ValueError('Invalid application Neo4j database')
    return value


def graph_session(driver):
    database=selected_database()
    return driver.session(database=database) if database else driver.session()
