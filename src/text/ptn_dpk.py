"""Static decoder for PtN DPK1/DBC1 containers and external table views."""
import struct
import bisect
from ptn_text_format import Reader, literal_tables


def packages(data):
    if data.startswith(b'DBC1'):
        yield None, data
        return
    magic, version, count, index, size, names, names_size, payload, payload_size = struct.unpack_from('<4sI7Q', data)
    if (magic,version)!=(b'DPK1',1) or size!=count*40 or index+size>len(data) or names+names_size>len(data) or payload+payload_size>len(data):
        raise ValueError('Invalid DPK1 directory')
    for i in range(count):
        start, length, _, _, offset, n, _=struct.unpack_from('<4I3Q',data,index+40*i)
        if start+length>names_size or offset<payload or offset+n>len(data):
            raise ValueError('Invalid DPK1 entry bounds')
        name=data[names+start:names+start+length].decode('ascii')
        yield name.replace('.','/')+'.lua',data[offset:offset+n]


def split(data):
    magic,ver,off,size,script,length=struct.unpack_from('<4sI4Q',data)
    if (magic,ver)!=(b'DBC1',1) or not 40<=off<=off+size<=script<=script+length<=len(data):
        raise ValueError('Invalid DBC1 payload bounds')
    return data[script:script+length],data[off:off+size]


class Data:
    def __init__(self,chunk,blob):
        self.blob=blob
        self.tables,self.diagnostics=literal_tables(*Reader(chunk).main(),blob=memoryview(blob))

    def view(self,spec, raw=False):
        kind,*args=spec
        if kind=='strpool':
            start,n,index=args
            offsets=self.view(index)
            if not offsets or offsets[0]!=0 or offsets[-1]!=n or not all(a<=b for a,b in zip(offsets,offsets[1:])):
                raise ValueError('Invalid string pool offsets')
            return [self.blob[start+a:start+b].decode('utf-8') for a,b in zip(offsets,offsets[1:])]
        dtype,start,n,*extra=args
        fmt={0:'d',1:'f',2:'q',3:'Q',4:'I',5:'i',6:'H',7:'h',8:'B',9:'b'}.get(dtype)
        if fmt is None:
            raise ValueError(f'Unsupported view type {dtype}')
        if raw and dtype in (0,1):fmt='Q' if dtype==0 else 'I'
        return [x[0] for x in struct.iter_unpack('<'+fmt,self.blob[start:start+n])]

    def language(self, ui=False):
        t=self.tables[0]
        ids,index,strings=(self.view(t[i]) for i in (1,2,3))
        if len(ids)!=len(index) or len(set(ids))!=len(ids) or not all(0<=i<=len(strings) for i in index):
            raise ValueError('Invalid localized text index')
        return dict(zip((str(i) for i in ids) if ui else ids, (strings[i-1] if i else '' for i in index))),strings

    def rows(self,localize):
        z=next((t for t in self.tables if b'fields' in t and b'proxy' in t),None)
        if not z:return
        cols=z[b'proxy'];names=z[b'names'];counts=self.view(z[b'counts'])
        def quads(key):
            v=self.view(z[key]);return list(zip(*(v[i::4] for i in range(4))))
        fields=quads(b'fields');specs=[]
        for si,(_,start,n,base) in enumerate(quads(b'structs')):
            sheet=[]
            for ni,col,flags,sub in (fields[start-1:start-1+n] if counts[si] else []):
                key=names[ni].decode('utf-8'); j=base+col
                try:
                    v=cols[j]
                    values=self.view(v,raw=bool(flags&128))
                    ends=None
                    if flags&128:
                        ends=values[::2];values=values[1::2]
                        bits={5:32,7:16,9:8}.get(v[1])
                        if bits:ends=[x & ((1<<bits)-1) for x in ends]
                        if len(ends)!=len(values) or (ends and ends[-1]!=counts[si]) or any(a>=b for a,b in zip(ends,ends[1:])):
                            raise ValueError('Invalid RLE boundaries')
                        if v[1] in (0,1):
                            fmt='d' if v[1]==0 else 'f'
                            bits='Q' if fmt=='d' else 'I'
                            values=[struct.unpack('<'+fmt,struct.pack('<'+bits,x))[0] for x in values]
                    elif len(values)!=counts[si]:
                        raise ValueError('Invalid column row count')
                    aux=self.view(cols[j+1]) if flags&0x50 else None
                    flat=self.view(cols[j+2]) if flags&0x10 else None
                    sheet.append((key,flags,sub,values,ends,aux,flat,cols.get(j+2)))
                except (KeyError,ValueError,TypeError,struct.error) as e:
                    self.diagnostics.append(f'{key}: {e}')
            specs.append(sheet)
        def row(si,i):
            result={}
            for key,flags,sub,values,ends,aux,flat,flat_spec in specs[si]:
                v=values[bisect.bisect_left(ends,i+1) if ends is not None else i]
                if flags&32:
                    prev=values[bisect.bisect_left(ends,i) if ends is not None else i-1] if i else 0
                    if not 0<=prev<=v<=counts[sub-1]:raise ValueError(f'Invalid child range {key}')
                    v=[row(sub-1,j) for j in range(prev,v)]
                elif flags&16:
                    if not 0<=v<=len(aux):raise ValueError(f'Invalid list index {key}')
                    a=aux[v-2] if v>1 else 0;b=aux[v-1] if v else 0
                    width=flat_spec[4] if flags&7==7 and len(flat_spec)>4 else 1
                    if not 0<=a<=b<=len(flat)//width:raise ValueError(f'Invalid list range {key}')
                    v=flat[a*width:b*width]
                    if flags&7==5:
                        result[key+'__text_ids']=[str(x) for x in v];v=[localize(x) for x in v]
                    elif width>1:v=[{str(j+1):x for j,x in enumerate(v[k:k+width])} for k in range(0,len(v),width)]
                else:
                    if flags&64:v=aux[v-1] if v else ''
                    if flags&7==5:result[key+'__text_id']=str(v);v=localize(v)
                    elif flags&7==1:v=bool(v)
                result[key]=v
            return result
        for i in range(counts[0]):
            yield row(0,i)
