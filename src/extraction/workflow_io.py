"""Strict JSON, atomic artifacts and exclusive run ownership (standard library)."""
import hashlib
import json
import os
import math
from pathlib import Path
import tempfile
import uuid


def _pairs(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('Duplicate JSON object key')
        result[key]=value
    return result


def _constant(value):
    raise ValueError('Non-finite JSON number: '+value)


def _float(value):
    parsed=float(value)
    if not math.isfinite(parsed):raise ValueError('Non-finite JSON numeric value')
    return parsed


def loads(text):
    if len(text)>16*1024*1024:raise ValueError('JSON document exceeds size limit')
    try:return json.loads(text,object_pairs_hook=_pairs,parse_constant=_constant,parse_float=_float)
    except RecursionError:raise ValueError('JSON nesting exceeds parser limit') from None


def read_json(path):
    with Path(path).open('rb') as stream:raw=stream.read(16*1024*1024+1)
    if len(raw)>16*1024*1024:raise ValueError('JSON document exceeds size limit')
    return loads(raw.decode('utf-8-sig'))


def canonical_hash(value):
    raw=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def file_hash(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path,value):
    path=Path(path)
    raw=json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,
                                         prefix='.'+path.name+'.',suffix='.tmp',delete=False) as stream:
            temporary=Path(stream.name)
            stream.write(raw);stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:
        if temporary is not None and temporary.exists():temporary.unlink()


class RunLock:
    def __init__(self,folder):
        self.path=Path(folder).resolve()/'.run.lock'
        self.token=uuid.uuid4().hex

    def __enter__(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        try:fd=os.open(self.path,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
        except FileExistsError:
            raise RuntimeError('Output is owned by another run or a stale lock; inspect .run.lock before recovery') from None
        try:
            with os.fdopen(fd,'w',encoding='utf-8') as stream:
                stream.write(json.dumps({'pid':os.getpid(),'token':self.token}))
                stream.flush();os.fsync(stream.fileno())
        except BaseException:
            self.path.unlink(missing_ok=True)
            raise
        return self

    def __exit__(self,*args):
        if self.path.exists() and read_json(self.path).get('token')==self.token:
            self.path.unlink()
