#!/bin/bash
echo 'local sel,occ,urg="","",""; for _,t in ipairs(require("awful").screen.focused().tags) do if t.selected then sel=sel..t.name end; if #t:clients()>0 then occ=occ..t.name end; if t.urgent then urg=urg..t.name end end; return sel.."|"..occ.."|"..urg' | awesome-client
