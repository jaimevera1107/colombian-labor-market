"""Conservative, self-contained BIFF8 (.xls OLE2) cell reader for DANE annexes.

It evaluates no formulas: it returns only the numeric results stored by Excel.
It rejects encryption, unsupported formats and truncated reads. It complements xlrd;
it does not try to replace a general Excel engine.
"""
from __future__ import annotations
import struct
from pathlib import Path

EOC=0xfffffffe
FREE=0xffffffff

class InvalidLegacyWorkbook(ValueError):pass

def _u16(b,o=0):return struct.unpack_from('<H',b,o)[0]
def _u32(b,o=0):return struct.unpack_from('<I',b,o)[0]

class _OLE:
 def __init__(self,path):
  self.data=Path(path).read_bytes()
  b=self.data
  if b[:8]!=bytes.fromhex('d0cf11e0a1b11ae1'):raise InvalidLegacyWorkbook('Not an OLE2 container')
  if b[28:30] != b'\xfe\xff':raise InvalidLegacyWorkbook('Unsupported OLE byte order')
  self.sec=1<<_u16(b,30);self.minisec=1<<_u16(b,32)
  if self.sec not in (512,4096):raise InvalidLegacyWorkbook('Unsupported sector size')
  self.cutoff=_u32(b,56)
  self.dir_sid=_u32(b,48)
  self.mini_fat_sid=_u32(b,60)
  self.minifat_count=_u32(b,64)
  dif_sid=_u32(b,68); dif_count=_u32(b,72)
  ids=[x for x in struct.unpack_from('<109I',b,76) if x!=FREE]
  for _ in range(dif_count):
   d=self.sector(dif_sid)
   parts=struct.unpack('<%dI'%(self.sec//4),d)
   ids.extend(x for x in parts[:-1] if x!=FREE)
   dif_sid=parts[-1]
  ids=ids[:_u32(b,44)]
  self.fat=[]
  for i in ids:self.fat.extend(struct.unpack('<%dI'%(self.sec//4),self.sector(i)))
  db=self.read_big(self.dir_sid,None)
  self.entries=[]
  for o in range(0,len(db)-127,128):
   e=db[o:o+128];sz=_u16(e,64);name=e[:max(0,sz-2)].decode('utf-16le','replace')
   self.entries.append((name,e[66],_u32(e,116),struct.unpack_from('<Q',e,120)[0]))
  root=self.entries[0]
  self.mini_stream=self.read_big(root[2],root[3]) if self.minifat_count else b''
  self.mini_fat=[]
  if self.minifat_count:
   mb=self.read_big(self.mini_fat_sid,self.minifat_count*self.sec)
   self.mini_fat=list(struct.unpack('<%dI'%(len(mb)//4),mb))
 def sector(self,sid):
  start=(sid+1)*self.sec
  if start+self.sec>len(self.data):raise InvalidLegacyWorkbook('Sector OLE fuera de archivo')
  return self.data[start:start+self.sec]
 def chain(self,sid,fat):
  seen=set()
  while sid not in (EOC,FREE):
   if sid in seen or sid>=len(fat):raise InvalidLegacyWorkbook('Cyclic/invalid FAT chain')
   seen.add(sid);yield sid;sid=fat[sid]
 def read_big(self,sid,size):
  b=b''.join(self.sector(i) for i in self.chain(sid,self.fat))
  if size is not None and len(b)<size:raise InvalidLegacyWorkbook('Flujo OLE truncado')
  return b if size is None else b[:size]
 def stream(self,name):
  e=next((e for e in self.entries if e[0].casefold()==name.casefold() and e[1]==2),None)
  if e is None:raise InvalidLegacyWorkbook(f'Stream {name} not found')
  if e[3]>=self.cutoff:return self.read_big(e[2],e[3])
  b=b''.join(self.mini_stream[i*self.minisec:(i+1)*self.minisec] for i in self.chain(e[2],self.mini_fat))
  if len(b)<e[3]:raise InvalidLegacyWorkbook('Miniflujo truncado')
  return b[:e[3]]

def _records(b,start=0,end=None):
 p=start;end=len(b) if end is None else end
 while p+4<=end:
  op,n=struct.unpack_from('<HH',b,p)
  if p+4+n>end:raise InvalidLegacyWorkbook('Registro BIFF truncado')
  yield p,op,b[p+4:p+4+n]
  p+=n+4

def _sst(segments):
 """SST with CONTINUE breaks, including encoding changes inside a string."""
 class Parts:
  def __init__(self,p):self.parts=p;self.i=0;self.k=0
  def read(self,n):
   out=bytearray()
   while n:
    if self.i>=len(self.parts):raise InvalidLegacyWorkbook('SST truncado')
    segment=self.parts[self.i]
    if self.k==len(segment):self.i+=1;self.k=0;continue
    a=min(n,len(segment)-self.k);out+=segment[self.k:self.k+a];self.k+=a;n-=a
   return bytes(out)
  def chars(self,n,wide):
   chunks=[]
   while n:
    if self.i>=len(self.parts):raise InvalidLegacyWorkbook('SST caracteres truncados')
    segment=self.parts[self.i]
    if self.k==len(segment):
     self.i+=1;self.k=0
     if self.i>=len(self.parts):raise InvalidLegacyWorkbook('CONTINUE faltante')
     wide=bool(self.read(1)[0]&1)
     continue
    width=2 if wide else 1
    available=(len(segment)-self.k)//width
    if not available:raise InvalidLegacyWorkbook('UTF-16 character split across records')
    take=min(n,available);v=self.read(take*width)
    chunks.append(v.decode('utf-16le' if wide else 'latin-1','replace'));n-=take
   return ''.join(chunks)
 p=Parts(segments)
 total=_u32(p.read(4));count=_u32(p.read(4));texts=[]
 if count>500000:raise InvalidLegacyWorkbook('SST excesivo')
 for _ in range(count):
  cch=_u16(p.read(2));flags=p.read(1)[0];wide=bool(flags&1)
  rich=_u16(p.read(2)) if flags&8 else 0
  ext=_u32(p.read(4)) if flags&4 else 0
  texts.append(p.chars(cch,wide))
  if rich:p.read(rich*4)
  if ext:p.read(ext)
 return texts

def _rk(raw):
 flags=raw&3;value=(raw>>2)
 if flags&2:
  if value & (1<<29):value-=1<<30
  result=float(value)
 else:result=struct.unpack('<d',struct.pack('<Q',(raw & 0xfffffffc)<<32))[0]
 return result/100 if flags&1 else result

def sheets(path):
 """Devuelve {nombre_hoja: matriz de valores}, solo resultados guardados."""
 wb=_OLE(path).stream('Workbook')
 sheet_meta=[];segments=[];in_sst=False;encrypted=False
 for pos,op,b in _records(wb):
  if op==0x85:
   offset=_u32(b);cch=b[6];wide=bool(b[7]&1)
   name=b[8:8+cch*(2 if wide else 1)].decode('utf-16le' if wide else 'latin-1','replace')
   sheet_meta.append((offset,name,b[5]))
  if op==0x2f:encrypted=True
  if op==0xfc:segments=[b];in_sst=True
  elif op==0x3c and in_sst:segments.append(b)
  elif in_sst:in_sst=False
  if op==0xa and sheet_meta:break
 if encrypted:raise InvalidLegacyWorkbook('Encrypted workbook not supported')
 strings=_sst(segments) if segments else []
 result={}
 for off,name,sheettype in sheet_meta:
  if sheettype!=0:continue
  cells={};maxrow=-1;maxcol=-1
  for pos,op,b in _records(wb,off):
   if op==0xa:break
   if op==0x203 and len(b)>=14:
    r,c=_u16(b),_u16(b,2);v=struct.unpack_from('<d',b,6)[0]
    cells[(r,c)]=v
   elif op==0xfd and len(b)>=10:
    r,c=_u16(b),_u16(b,2);idx=_u32(b,6)
    if idx>=len(strings):raise InvalidLegacyWorkbook('SST index fuera de rango')
    cells[(r,c)]=strings[idx]
   elif op==0x27e and len(b)>=10:
    r,c=_u16(b),_u16(b,2);cells[(r,c)]=_rk(_u32(b,6))
   elif op==0xbd and len(b)>=6:
    r,c=_u16(b),_u16(b,2);last=_u16(b,len(b)-2)
    if len(b)!=6*(last-c+1)+6:raise InvalidLegacyWorkbook('MULRK of unexpected size')
    for j in range(last-c+1):cells[(r,c+j)]=_rk(_u32(b,6+j*6))
   elif op==0x6 and len(b)>=20:
    r,c=_u16(b),_u16(b,2)
    # Non-numeric or pending results are skipped: formulas are never evaluated.
    if b[12:14]!=b'\xff\xff':cells[(r,c)]=struct.unpack_from('<d',b,6)[0]
   elif op==0x204 and len(b)>=9:
    r,c=_u16(b),_u16(b,2);chars=_u16(b,6);flag=b[8];size=2 if flag&1 else 1
    cells[(r,c)]=b[9:9+chars*size].decode('utf-16le' if size==2 else 'latin-1','replace')
   elif op==0x205 and len(b)>=8:
    r,c=_u16(b),_u16(b,2);cells[(r,c)]=bool(b[6]) if not b[7] else None
   else:continue
   if op in (0x203,0xfd,0x27e,0xbd,0x6,0x204,0x205):
    maxrow=max(maxrow,r);maxcol=max(maxcol,c)
  # Files can include styling thousands of rows beyond populated cells; never pad to formatting dimensions.
  if maxrow>65535 or maxcol>255:raise InvalidLegacyWorkbook('Invalid BIFF dimensions')
  rows=[[None]*(maxcol+1) for _ in range(maxrow+1)]
  for (r,c),v in cells.items():rows[r][c]=v
  result[name]=rows
 return result
