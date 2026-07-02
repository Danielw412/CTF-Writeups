set pagination off
set confirm off
cd /tmp/oas_len_probe
break *0x408980
run quiz
dump memory /tmp/tgtshape_entries_blockctx.bin *(void**)0x618ca8 (*(void**)0x618ca8)+0x210
dump memory /tmp/tgtshape_stack_408980.bin $rsp $rsp+0x140
info registers rax rbx rcx rdx rsi rdi rbp rsp r8 r9 r10 r11 r12 r13 r14 r15
x/gx 0x618cd8
x/gx 0x618cc0
x/gx 0x618cc8
quit
