#!/bin/bash
echo 'local s=""; for _, t in ipairs(require("awful").screen.focused().selected_tags) do s=s..t.name end; return s' | awesome-client
