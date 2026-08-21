import win32file, pywintypes, time
start = time.time()
while time.time() - start < 2:
    try:
        handle = win32file.CreateFile(
            r'\\.\pipe\revit-mcp',
            win32file.GENERIC_READ | win32file.GENERIC_WRITE,
            0, None, win32file.OPEN_EXISTING, 0, None
        )
        print('Pipe exists!')
        win32file.CloseHandle(handle)
        break
    except pywintypes.error as e:
        if e.winerror == 2:  # FILE_NOT_FOUND
            time.sleep(0.1)
        else:
            print('Pipe error:', e.winerror, e.strerror)
            break
else:
    print('Pipe not found after 2 seconds')