set pagination off
set confirm off
cd /tmp/oas_len_probe_rand
break *0x408980
condition 1 $r15 == (*(void**)0x618ca8 + 0x108) && $rbx == 0
run quiz
dump memory /tmp/rand_entries_real_blockctx.bin *(void**)0x618ca8 (*(void**)0x618ca8)+0x210
x/gx 0x618cd8
x/gx 0x618cc0
x/gx 0x618cc8
quit
set pagination off
set confirm off
cd /tmp/oas_len_probe_61082
break *0x408980
condition 1 $r15 == (*(void**)0x618ca8 + 0x108) && $rbx == 0
run quiz
dump memory /tmp/entries_61082_real_blockctx.bin *(void**)0x618ca8 (*(void**)0x618ca8)+0x210
x/gx 0x618cd8
x/gx 0x618cc0
x/gx 0x618cc8
quit
