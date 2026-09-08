import adsk.core
import adsk.fusion
from pathlib import Path

def run(context):
    application=adsk.core.Application.get()
    if adsk.fusion.Design.cast(application.activeProduct) is None:
        application.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
    Path('E:/CyberArm/mechanical/logs/fusion_hardware_bootstrap_status.txt').write_text('Hardware inspection document ready',encoding='utf-8')
