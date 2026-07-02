set pagination off
set confirm off
set verbose off
set logging file /tmp/oas_tail_log.txt
set logging overwrite on
set logging enabled on

python
import gdb

BASE_ENTRIES = 0x618ca8
N_ENTRIES = 0x618cb0

def u64(addr):
    return int(gdb.parse_and_eval("*(unsigned long long*)%#x" % addr)) & ((1 << 64) - 1)

def reg(name):
    return int(gdb.parse_and_eval("$" + name)) & ((1 << 64) - 1)

def recidx():
    rsp = reg("rsp")
    return u64(rsp + 0x50)

def ptr_to_global(ptr):
    n = u64(N_ENTRIES)
    for i in range(n):
        ent = u64(BASE_ENTRIES) + i * 0x108
        count = u64(ent + 0x88)
        start = u64(ent + 0x90)
        buf = u64(ent + 0x70)
        if buf <= ptr < buf + count * 64:
            return start + ((ptr - buf) // 64)
    return None

class LogPtr(gdb.Breakpoint):
    def __init__(self, spec, regname):
        super().__init__(spec, internal=False)
        self.silent = True
        self.regname = regname

    def stop(self):
        ptr = reg(self.regname)
        gi = ptr_to_global(ptr)
        print("REC %d PTR_%s %#x GI %s" % (recidx(), self.regname, ptr, "None" if gi is None else str(gi)))
        return False

LogPtr("*0x40bbef", "rsi")
LogPtr("*0x40c9f1", "rcx")
LogPtr("*0x40cb12", "rdi")
LogPtr("*0x40cee5", "rdx")
end

run quiz
