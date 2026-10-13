"""Bounded image batches, using the existing image encoder one file at a time."""
from pathlib import Path
from types import SimpleNamespace
import zipfile

from pypdf import PdfReader, PdfWriter

from .converters import convert_image, checkpoint, update, ConversionError


def convert_images(job):
    if len(job.sources) == 1:
        return convert_image(job)
    outputs, names, used = [], [], set()
    total = 0
    for index, (source, original) in enumerate(zip(job.sources, job.filenames)):
        checkpoint(job)
        update(job, 5 + 75 * index / len(job.sources), f'Converting image {index + 1} of {len(job.sources)}')
        # A numbered intermediate name cannot collide with another source/result.
        child = SimpleNamespace(sources=[source], filenames=[f'batch-{index + 1}'], options=job.options,
                                directory=job.directory, cancel=job.cancel, warnings=job.warnings, progress=0, stage='')
        output = convert_image(child)
        total += output.stat().st_size
        if total > 500_000_000:
            raise ConversionError('Converted images exceed 500 MB. Choose a smaller batch or maximum width.')
        base = Path(original).stem[:140] or 'image'
        extension = job.options['format']
        name, suffix = f'{base}-converted.{extension}', 2
        while name.lower() in used:
            name = f'{base}-converted-{suffix}.{extension}'; suffix += 1
        used.add(name.lower()); names.append(name); outputs.append(output)
    checkpoint(job)
    if job.options['format'] == 'pdf':
        result = job.directory / 'images.pdf'
        writer = PdfWriter()
        try:
            for output in outputs:
                checkpoint(job)
                for page in PdfReader(output).pages:
                    writer.add_page(page)
            update(job, 90, 'Writing combined image PDF')
            with result.open('wb') as stream:
                writer.write(stream)
        finally:
            writer.close()
    else:
        result = job.directory / 'images.zip'
        with zipfile.ZipFile(result, 'w', compression=zipfile.ZIP_STORED) as archive:
            for output, name in zip(outputs, names):
                checkpoint(job); archive.write(output, name)
    return result
