from PyQt6.QtCore import QMetaObject, Qt, Q_ARG
import inspect

print(dir(QMetaObject))
print("---")
                                
sigs = [x for x in dir(QMetaObject) if 'invoke' in x.lower()]
print(sigs)
