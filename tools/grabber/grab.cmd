@echo off
REM Wrapper so you can: grab.cmd <url1> <url2> ...
REM Or:  grab.cmd --list mylist.txt --concurrent 4
python "D:\CLAUDE\tools\grabber\grab.py" %*
