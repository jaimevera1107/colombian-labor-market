"""Minimal read-only OLE2/BIFF8 extractor for a legacy DANE .xls.
Pure stdlib; never modifies source. Only supports numeric/string cell records.
"""
import struct, collections

def ole_streams(path):
    b=open(path,'rb').read()
    assert b[:8]==bytes.fromhex('d0cf11e0a1b11ae1'), 'Not OLE2'
    u16=lambda o:struct.unpack_from('<H',b,o)[0]
    u32=lambda o:struct.unpack_from('<I',b,o)[0]
    secsize=1<<u16(0x1e); minisecsize=1<<u16(0x20)
    def sec(s):return b[(s+1)*secsize:(s+2)*secsize]
    fid=list(struct.unpack_from('<109I',b,0x4c))
    fat_count=u32(0x2c); first_difat=u32(0x44); difat_count=u32(0x48)
    d=first_difat
    for _ in range(difat_count):
        block=sec(d); fid.extend(struct.unpack_from('<%dI'%((secsize//4)-1),block))
        d=struct.unpack_from('<I',block,secsize-4)[0]
    fids=fid[:fat_count]
    fat=[]
    for s in fids:fat.extend(struct.unpack('<%dI'%(secsize//4),sec(s)))
    def chain(first,table,maxn=100000):
        res=[]; cur=first
        while cur<0xFFFFFFF0 and len(res)<maxn:
            assert cur<len(table),('invalid chain sector',cur)
            res.append(cur)
            cur=table[cur]
        return res
    dirs=b''.join(sec(s) for s in chain(u32(0x30),fat))
    entries=[]
    for i in range(0,len(dirs),128):
        ent=dirs[i:i+128]
        if len(ent)<128:break
        nlen=struct.unpack_from('<H',ent,64)[0]
        name=ent[:max(0,nlen-2)].decode('utf-16le','replace') if nlen else ''
        typ=ent[66];first=struct.unpack_from('<I',ent,116)[0]
        length=struct.unpack_from('<Q',ent,120)[0]
        entries.append((name,typ,first,length))
    root=next(x for x in entries if x[1]==5)
    mini_stream=b''.join(sec(s) for s in chain(root[2],fat))[:root[3]]
    mf=[]
    for s in chain(u32(0x3c),fat):mf.extend(struct.unpack('<%dI'%(secsize//4),sec(s)))
    out={}
    for name,typ,first,length in entries:
        if typ!=2:continue
        if length<u32(0x38):
            raw=b''.join(mini_stream[s*minisecsize:(s+1)*minisecsize] for s in chain(first,mf))[:length]
        else:
            raw=b''.join(sec(s) for s in chain(first,fat))[:length]
        out[name]=raw
    return out

def records(stream,begin=0,end=None):
    end=len(stream) if end is None else end
    pos=begin
    while pos+4<=end:
        opcode,n=struct.unpack_from('<HH',stream,pos)
        if pos+4+n>end:break
        yield pos,opcode,stream[pos+4:pos+4+n]
        pos+=n+4

def parse_workbook(stream):
    # Parse global record zone to get BOUNDSHEET and SST with CONTINUE blocks.
    sheets=[];sst_parts=[]; in_sst=False
    for p,op,data in records(stream):
        if op==0x0085:
            offset=struct.unpack_from('<I',data,0)[0]
            count=data[6]; flags=data[7]
            name=(data[8:8+2*count].decode('utf-16le','replace') if flags&1 else data[8:8+count].decode('latin1','replace'))
            sheets.append((name,offset))
        if op==0x00FC:sst_parts=[data];in_sst=True
        elif op==0x003C and in_sst:sst_parts.append(data)
        elif in_sst:in_sst=False
        if op==0x000A:break
    # Short SST decoder with boundaries at CONTINUE records. Sometimes strings may split over records
    sst=[]
    if sst_parts:
        data=b''.join(sst_parts)
        total,unique=struct.unpack_from('<II',data,0);pos=8
        for si in range(unique):
            if pos+3>len(data):break
            n,flags=struct.unpack_from('<HB',data,pos);pos+=3
            rich=struct.unpack_from('<H',data,pos)[0] if flags&8 else 0
            if flags&8:pos+=2
            ext=struct.unpack_from('<I',data,pos)[0] if flags&4 else 0
            if flags&4:pos+=4
            unicode_=flags&1
            width=2 if unicode_ else 1
            raw=data[pos:pos+width*n];pos+=width*n
            sst.append(raw.decode('utf-16le' if unicode_ else 'latin1','replace'))
            pos+=rich*4+ext
        if len(sst)!=unique:
            print('WARN: short SST',len(sst),unique)
    tables={}
    for idx,(name,start) in enumerate(sheets):
        end=sheets[idx+1][1] if idx+1<len(sheets) else len(stream)
        vals={}
        for p,op,d in records(stream,start,end):
            if op==0x00FD and len(d)>=10:
                row,col,xf,sti=struct.unpack_from('<HHHI',d)
                vals[(row,col)]=sst[sti] if sti<len(sst) else f'[SST:{sti}]'
            elif op==0x0203 and len(d)>=14:
                row,col,xf=struct.unpack_from('<HHH',d)
                vals[(row,col)]=struct.unpack_from('<d',d,6)[0]
            elif op==0x027E and len(d)>=10:
                row,col,xf,v=struct.unpack_from('<HHHI',d)
                vals[(row,col)]=rk(v)
            elif op==0x00BD and len(d)>=6:
                row,startcol=struct.unpack_from('<HH',d)
                n=(len(d)-6)//6
                for i in range(n):vals[(row,startcol+i)]=rk(struct.unpack_from('<I',d,6+i*6-4)[0]) if False else rk(struct.unpack_from('<I',d,4+i*6+2)[0])
            elif op==0x0204 and len(d)>=8:
                row,col,xf,l=struct.unpack_from('<HHHH',d)
                vals[(row,col)]=d[8:8+l].decode('latin1','replace')
            elif op==0x0006 and len(d)>=20:
                row,col,xf=struct.unpack_from('<HHH',d)
                result=d[6:14]
                if result[6:8]!=b'\xff\xff':vals[(row,col)]=struct.unpack('<d',result)[0]
            elif op==0x000A:break
        tables[name]=vals
    return tables

def rk(v):
    if v&2:
        ans=(v>>2)
        if ans&0x20000000:ans-=0x40000000
    else:
        ans=struct.unpack('<d',struct.pack('<Q',(v&0xFFFFFFFC)<<32))[0]
    if v&1:ans/=100
    return ans

if __name__=='__main__':
    p='/mnt/data/CNPV-2018-Poblacion-Ajustada-por-Cobertura.xls'
    ss=ole_streams(p)
    print('streams',[(k,len(v)) for k,v in ss.items()])
    tables=parse_workbook(ss.get('Workbook',ss.get('Book',b'')))
    for name,vals in tables.items():
        print('SHEET',name,'cells',len(vals),'bounds',max(x[0] for x in vals),max(x[1] for x in vals))
        for r in range(25):
            print(r,[(c,vals[r,c]) for c in range(25) if (r,c) in vals])
