set pagination off
set confirm off
cd /tmp/oas_len_probe
break *0x408650
run quiz
dump memory /tmp/tgtshape_entries.bin *(void**)0x618ca8 (*(void**)0x618ca8)+0x210
x/gx 0x618cd8
x/gx 0x618cc0
x/gx 0x618cc8
quit
