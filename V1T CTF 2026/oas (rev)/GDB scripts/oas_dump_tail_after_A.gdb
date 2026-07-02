set pagination off
set confirm off
cd /tmp/oas_len_probe
break *0x40df58
run quiz
set $buf = *(void**)($rsp+0x20)
set $len = *(long*)($rsp+0x18)
dump memory /tmp/tail_before_400f60_A.bin $buf $buf+$len
finish
dump memory /tmp/tail_after_400f60_A.bin $buf $buf+$len
continue
quit
