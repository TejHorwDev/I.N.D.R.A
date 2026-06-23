from PyQt6.QtCore import QMetaObject, Qt, Q_ARG
import inspect

# Check what overloads are available
print(dir(QMetaObject))
print("---")
# Look at invokeMethod signature
sigs = [x for x in dir(QMetaObject) if 'invoke' in x.lower()]
print(sigs)
