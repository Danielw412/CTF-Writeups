set pagination off
set confirm off
cd /tmp/oas_len_probe_61082
break *0x4052d3
run quiz
dump memory /tmp/header_61082_plain.bin $rsp+0x50 $rsp+0x90
x/8gx $rsp+0x50
continue
quit
