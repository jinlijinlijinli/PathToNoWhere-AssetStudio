"""Read the observed PtN XX bytecode format without executing game scripts."""
import struct


class Reader:
    def __init__(self, data):
        if not data.startswith(b'\x1bXX\x07\x04\x08\x08\x01'):
            raise ValueError('Unsupported XX chunk header')
        self.data = data
        self.pos = 8
        self.strings = []

    def take(self, size):
        if size < 0 or self.pos + size > len(self.data):
            raise ValueError('Truncated chunk')
        value = self.data[self.pos:self.pos+size]
        self.pos += size
        return value

    def varint(self):
        value = 0
        for _ in range(10):
            byte = self.take(1)[0]
            value = (value << 7) | (byte & 127)
            if byte < 128:
                return value
        raise ValueError('Invalid variable integer')

    def string(self):
        size = self.varint()
        if size == 0:
            reference = self.varint()
            if reference == 0:
                return b''
            if reference>len(self.strings):
                raise ValueError('Invalid interned string reference')
            return self.strings[reference-1]
        value = self.take(size)
        if value[-1:]!=b'\0':
            raise ValueError('String terminator missing')
        value = value[:-1]
        self.strings.append(value)
        return value

    def main(self):
        self.varint()
        self.varint()
        self.take(3)
        count = self.varint()
        self.pos = (self.pos+3)//4*4
        code = [v[0] for v in struct.iter_unpack('<I', self.take(count*4))]
        constants = []
        for index in range(self.varint()):
            offset = self.pos
            tag = self.take(1)[0]
            if tag in (0, 1, 17):
                value = None if tag == 0 else tag == 17
            elif tag in (3, 35):
                number = self.varint()
                value = (number >> 1) ^ -(number & 1)
            elif tag == 19:
                value = struct.unpack('<d', self.take(8))[0]
            elif tag in (4, 20):
                value = self.string()
            else:
                raise ValueError('Unknown constant tag: '+str(tag))
            constants.append({'index':index, 'offset':offset, 'tag':tag, 'value':value})
        return code, constants

    def functions(self):
        """Read nested prototypes and their debug records in the observed format."""
        functions = []
        def string():
            return self.string()

        def prototype(depth=0):
            if depth>100:
                raise ValueError('Prototype nesting limit exceeded')
            code, constants = self.main()
            record = {'prototypeIndex':len(functions),'code':code,'constants':constants}
            functions.append(record)
            self.take(self.varint()*3)
            children = self.varint()
            for _ in range(children):
                prototype(depth+1)
            record['source'] = string().decode('utf-8',errors='replace')
            self.take(self.varint())
            absolute_lines = self.varint()
            if absolute_lines:
                self.pos = (self.pos+3)//4*4
                self.take(absolute_lines*8)
            for _ in range(self.varint()):
                string()
                self.varint()
                self.varint()
            for _ in range(self.varint()):
                string()
        prototype()
        if self.data[self.pos:].strip(b'\0'):
            raise ValueError('Unconsumed bytes after prototypes')
        return functions


def unwrap(data):
    """Read root field 1: vector of tables, each with field 0 byte vector."""
    def u32(pos):
        if pos < 0 or pos+4 > len(data):
            raise ValueError('Invalid FlatBuffer position')
        return struct.unpack_from('<I', data, pos)[0]

    def field(table, index):
        vt = table - struct.unpack_from('<i', data, table)[0]
        if vt < 0 or vt+4 > len(data):
            raise ValueError('Invalid vtable')
        length = struct.unpack_from('<H', data, vt)[0]
        entry = vt+4+index*2
        if entry+2 > vt+length:
            raise ValueError('Missing field')
        offset = struct.unpack_from('<H', data, entry)[0]
        if not offset:
            raise ValueError('Empty field')
        return table+offset

    root = u32(0)
    fp = field(root, 1)
    entries_vector = fp+u32(fp)
    count = u32(entries_vector)
    if count > len(data)//4:
        raise ValueError('Invalid vector count')
    for index in range(count):
        entry = entries_vector+4+index*4
        table = entry+u32(entry)
        fp = field(table, 0)
        vector = fp+u32(fp)
        size = u32(vector)
        start = vector+4
        if start+size > len(data):
            raise ValueError('Truncated payload')
        yield index, start, data[start:start+size]


def readable(value):
    if not isinstance(value, bytes):
        return None
    try:
        text = value.decode('utf-8')
    except UnicodeDecodeError:
        return None
    if any(ord(ch) < 32 and ch not in '\r\n\t' for ch in text):
        return None
    return text


def literal_tables(code, constants):
    """Statically evaluate only literal initialization operations, never script calls.

    Known dim.array constructors decode packed numeric arrays. Unknown functions
    are not run; their result becomes None. This is not a general Lua interpreter.
    """
    constants = [c['value'] for c in constants]
    regs = {}
    tables = []
    diagnostics = set()
    formats = {'int8':'b','uint8':'B','int16':'h','uint16':'H','int32':'i','uint32':'I','int64':'q','uint64':'Q','float':'f','double':'d'}

    def get(table, key):
        if table == '__dim__':
            name = readable(key)
            return '__array__' if name == 'array' else '__dtype__'+str(name)
        return table.get(key) if isinstance(table, dict) else None

    index = 0
    top = 0
    while index < len(code):
        word = code[index]
        op, a, k, b, c = word&127, (word>>7)&255, (word>>15)&1, (word>>16)&255, word>>24
        bx = word>>15
        if op == 0:
            regs[a] = regs.get(b)
        elif op in (1, 2):
            regs[a] = bx-65535
        elif op == 4:
            regs[a] = constants[bx]
        elif op == 5:
            index += 1
            regs[a] = constants[code[index]>>7]
        elif op in (6, 8):
            regs[a] = op == 8
        elif op == 9:
            for register in range(a, a+b+1):
                regs[register] = None
        elif op == 12:
            name = readable(constants[c])
            regs[a] = '__dim__' if name == 'dim' else '__global__'+str(name)
        elif op in (13, 14, 15):
            key = regs.get(c) if op == 13 else c if op == 14 else constants[c]
            regs[a] = get(regs.get(b), key)
        elif op in (17, 18, 19):
            table = regs.get(a)
            key = regs.get(b) if op == 17 else b if op == 18 else constants[b]
            value = constants[c] if k else regs.get(c)
            if isinstance(table, dict) and isinstance(key, (bytes, str, int, float)):
                table[key] = value
        elif op == 20:
            table = {}
            tables.append(table)
            regs[a] = table
            index += 1  # this format always includes an EXTRAARG after NEWTABLE
        elif op == 71:
            function = regs.get(a)
            arguments = [regs.get(j) for j in range(a+1,a+b)]
            if function == '__array__' and len(arguments) == 2:
                dtype, packed = arguments
                fmt = formats.get(dtype.removeprefix('__dtype__')) if isinstance(dtype,str) else None
                if fmt and isinstance(packed,bytes) and len(packed)%struct.calcsize(fmt)==0:
                    regs[a] = [v[0] for v in struct.iter_unpack('<'+fmt, packed)]
                else:
                    regs[a] = None
                    diagnostics.add('unsupported dim.array')
            else:
                regs[a] = None
                diagnostics.add('unexecuted function call')
            if c == 0:
                top = a+1
        elif op == 81:
            start = c
            if k:
                index += 1
                start += (code[index]>>7)*256
            start *= 4
            table = regs.get(a)
            if isinstance(table,dict):
                count = b if b else max(0,top-a-1)
                for offset in range(1,count+1):
                    table[start+offset] = regs.get(a+offset)
        index += 1
    return tables, sorted(diagnostics)
