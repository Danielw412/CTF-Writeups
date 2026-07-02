set pagination off
set confirm off
set verbose off

python
import gdb
import struct

TARGET = "/home/techadmin/ctf/rev/oas/quiz.oas"
TOTAL = 2514
TAIL0 = 64 + TOTAL * 64
CC8 = 0x40fe2443a3750795

data = open(TARGET, "rb").read()
q2s = [struct.unpack_from("<Q", data, TAIL0 + 88 * i + 16)[0] for i in range((len(data) - TAIL0) // 88)]

def u64(addr):
    return int(gdb.parse_and_eval("*(unsigned long long*)%#x" % addr)) & ((1 << 64) - 1)

def reg(name):
    return int(gdb.parse_and_eval("$" + name)) & ((1 << 64) - 1)

class ForceTargetKeystream(gdb.Breakpoint):
    def __init__(self):
        super().__init__("*0x40bde8", internal=False)
        self.silent = True

    def stop(self):
        rsp = reg("rsp")
        rec = u64(rsp + 0x50)
        q0 = u64(rsp + 0x18)
        q2 = q2s[rec]
        seed = CC8 ^ q0 ^ q2
        inferior = gdb.selected_inferior()
        inferior.write_memory(rsp + 0x60, struct.pack("<Q", q2))
        inferior.write_memory(rsp, struct.pack("<Q", seed))
        inferior.write_memory(reg("r15"), b"\x00" * 64)
        return False

ForceTargetKeystream()
end

run quiz
