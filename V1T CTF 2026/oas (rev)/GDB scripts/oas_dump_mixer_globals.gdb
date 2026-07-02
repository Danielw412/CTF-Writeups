set pagination off
set confirm off
cd /tmp/oas_len_probe
break *0x408980
condition 1 $r15 == (*(void**)0x618ca8 + 0x108) && $rbx == 0
run quiz
x/8gx 0x618cc0
quit
