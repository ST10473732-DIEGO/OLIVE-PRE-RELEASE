"""Only bounded re-encoded raster CID images can enter a mail display document."""
import base64
import io
from PIL import Image


def inline_images(local,record_id):
    record=local.get(record_id);result={};total=0
    for attachment in record['attachments']:
        if not attachment.get('cid') or attachment['type'] not in {'image/png','image/jpeg','image/gif','image/webp'}:continue
        if attachment['size']>2_000_000 or len(result)>=10:continue
        with local.store.transaction() as db:data=local.store.read_blob(db,attachment['hash'])
        try:
            with Image.open(io.BytesIO(data)) as source:
                if source.width*source.height>4_000_000:continue
                source.seek(0);image=source.convert('RGBA');image.thumbnail((1200,1200))
                target=io.BytesIO();image.save(target,format='PNG');encoded=target.getvalue()
        except (OSError,ValueError,Image.DecompressionBombError):continue
        if total+len(encoded)>500_000:continue
        total+=len(encoded);result[attachment['cid']]='data:image/png;base64,'+base64.b64encode(encoded).decode('ascii')
    return {'images':result,'remote_resources':'blocked'}
