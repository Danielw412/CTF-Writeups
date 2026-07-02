set pagination off
set confirm off
cd /tmp/oas_len_probe
break *0x40df58
run quiz
set $buf = *(void**)($rsp+0x20)
set $len = *(long*)($rsp+0x18)
printf "before buf=%p len=%lu\n", $buf, $len
dump memory /tmp/tail_plain_A.bin $buf $buf+$len
stepi
printf "after key=%016lx len=%lu\n", *(unsigned long long*)0x618ce8, $len
dump memory /tmp/tail_cipher_mem_A.bin $buf $buf+$len
continue
quit
set pagination off
set confirm off
cd /tmp/oas_len_probe_rand
break *0x40df58
run quiz
set $buf = *(void**)($rsp+0x20)
set $len = *(long*)($rsp+0x18)
printf "before buf=%p len=%lu\n", $buf, $len
dump memory /tmp/tail_plain_rand.bin $buf $buf+$len
stepi
dump memory /tmp/tail_cipher_mem_rand.bin $buf $buf+$len
continue
quit
