"""Set the running macOS Dock icon independently of the launcher icon."""
import ctypes
import os
import sys


def set_dock_icon(path):
    if sys.platform != 'darwin':
        return False
    ctypes.CDLL('/System/Library/Frameworks/AppKit.framework/AppKit')
    objc = ctypes.CDLL('/usr/lib/libobjc.A.dylib')
    pointer = ctypes.c_void_p
    objc.objc_getClass.argtypes = [ctypes.c_char_p]
    objc.objc_getClass.restype = pointer
    objc.sel_registerName.argtypes = [ctypes.c_char_p]
    objc.sel_registerName.restype = pointer
    send = ctypes.CFUNCTYPE(pointer, pointer, pointer)(('objc_msgSend', objc))
    send_arg = ctypes.CFUNCTYPE(pointer, pointer, pointer, pointer)(('objc_msgSend', objc))
    send_text = ctypes.CFUNCTYPE(pointer, pointer, pointer, ctypes.c_char_p)(('objc_msgSend', objc))
    send_void = ctypes.CFUNCTYPE(None, pointer, pointer, pointer)(('objc_msgSend', objc))
    selector = lambda name: objc.sel_registerName(name.encode())
    string = send_text(objc.objc_getClass(b'NSString'), selector('stringWithUTF8String:'), os.fsencode(path))
    allocated = send(objc.objc_getClass(b'NSImage'), selector('alloc'))
    image = send_arg(allocated, selector('initWithContentsOfFile:'), string)
    if not image:
        return False
    app = send(objc.objc_getClass(b'NSApplication'), selector('sharedApplication'))
    send_void(app, selector('setApplicationIconImage:'), image)
    # NSApplication retains its icon. Release our ownership.
    ctypes.CFUNCTYPE(None, pointer, pointer)(('objc_msgSend', objc))(image, selector('release'))
    return True
