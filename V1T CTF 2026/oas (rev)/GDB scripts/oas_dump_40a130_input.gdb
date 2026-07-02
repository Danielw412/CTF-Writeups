set pagination off
set confirm off
cd /tmp/oas_len_probe
break *0x40a130
ignore 1 1
run quiz
printf "rdi=%p rsi=%lu rdx=%p\n", $rdi, $rsi, $rdx
dump memory /tmp/tgtshape_real_40a130_input.bin $rdi $rdi+$rsi
continue
quit
