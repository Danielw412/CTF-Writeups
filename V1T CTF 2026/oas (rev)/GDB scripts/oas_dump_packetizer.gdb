set pagination off
set confirm off
cd /tmp/oas_len_probe
break *0x408650
run quiz
set $e = *(void**)0x618ca8 + 0x108
dump memory /tmp/tgtshape_real_plus60.bin *(void**)($e+0x60) (*(void**)($e+0x60))+*(long*)($e+0x78)
dump memory /tmp/tgtshape_real_plus68.bin *(void**)($e+0x68) (*(void**)($e+0x68))+*(long*)($e+0x80)
x/gx $e+0x78
x/gx $e+0x80
x/gx $e+0x88
quit
