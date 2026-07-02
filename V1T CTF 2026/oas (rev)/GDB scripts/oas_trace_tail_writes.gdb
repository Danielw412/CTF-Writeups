set pagination off
set confirm off
cd /tmp/oas_len_probe
set $cnt = 0
break *0x4009d0 if $rdx == 8
commands
  silent
  if $cnt < 12
    printf "write8 cnt=%ld ret=%p buf=%p val=%016lx\n", $cnt, *(void**)$rsp, $rsi, *(unsigned long long*)$rsi
    set $cnt = $cnt + 1
  end
  continue
end
run quiz
quit
