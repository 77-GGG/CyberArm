"""Independent STL-byte validation, reusing the read-only RevB checker."""
from pathlib import Path
script=Path('E:/CyberArm/mechanical/scripts/revB_verify_stl.py').read_text(encoding='utf8')
script=script.replace("archive/arduino_reference_revB","arduino_reference_revC").replace("['STL_FIT_REVIEW_mm','PRINT_FIRST_horn_tests_mm']","['STL_RevC_mm','PRINT_FIRST_RevC_mm']")
exec(compile(script,'revC_binary_STL_check','exec'),{'__name__':'__main__'})
