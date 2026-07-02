set pagination off
set confirm off
set verbose off

python
import gdb
import struct

TARGET = "/home/techadmin/ctf/rev/oas/quiz.oas"
SCHEDULE = "/tmp/oas_tail_schedule.tsv"
TOTAL = 2514
TAIL0 = 64 + TOTAL * 64
CC8 = 0x40fe2443a3750795
FEEDFACE = 0xfeedface

data = open(TARGET, "rb").read()
records = (len(data) - TAIL0) // 88
stored_q2s = [struct.unpack_from("<Q", data, TAIL0 + 88 * i + 16)[0] for i in range(records)]

arities = []
for line in open(SCHEDULE, "r"):
    idx, body = line.rstrip("\n").split("\t")
    parts = [x for x in body.split(",") if x]
    if int(idx) != len(arities):
        raise RuntimeError("schedule index mismatch")
    arities.append(len(parts))
if len(arities) != records:
    raise RuntimeError("schedule length mismatch")

def u64(addr):
    return int(gdb.parse_and_eval("*(unsigned long long*)%#x" % addr)) & ((1 << 64) - 1)

def reg(name):
    return int(gdb.parse_and_eval("$" + name)) & ((1 << 64) - 1)

class ForceTargetKeystream(gdb.Breakpoint):
    def __init__(self):
        super().__init__("*0x40bdd8", internal=False)
        self.silent = True

    def stop(self):
        rsp = reg("rsp")
        rec = u64(rsp + 0x50)
        q0 = u64(rsp + 0x18)
        stored_q2 = stored_q2s[rec]
        toggled = ((q0 & 63) == 42) or (arities[rec] == 5 and (q0 & 7) == 3)
        pre_q2 = stored_q2 ^ (FEEDFACE if toggled else 0)
        seed = CC8 ^ q0 ^ pre_q2
        inferior = gdb.selected_inferior()
        inferior.write_memory(rsp + 0x60, struct.pack("<Q", pre_q2))
        inferior.write_memory(rsp, struct.pack("<Q", seed))
        inferior.write_memory(reg("r15"), b"\x00" * 64)
        return False

ForceTargetKeystream()
end

run quiz
