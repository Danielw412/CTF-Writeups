set pagination off
set confirm off
set verbose off

python
import gdb

def reg(name):
    return int(gdb.parse_and_eval("$" + name)) & ((1 << 64) - 1)

class ZeroTailPayload(gdb.Breakpoint):
    def __init__(self):
        super().__init__("*0x40bdd8", internal=False)
        self.silent = True

    def stop(self):
        gdb.selected_inferior().write_memory(reg("r15"), b"\x00" * 64)
        return False

ZeroTailPayload()
end

run quiz
