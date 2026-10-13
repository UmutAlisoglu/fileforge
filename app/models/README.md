# Offline background removal model

FileForge 0.2.0 bundles the unmodified U²-Net small (U2NETP) model by Xuebin Qin and contributors, under Apache-2.0. The Windows application can remove backgrounds without downloading a model at runtime or sending the picture to an AI service.

- Architecture and source: https://github.com/xuebinqin/U-2-Net
- ONNX weights distributed by rembg: https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2netp.onnx
- Preprocessing reference: https://github.com/danielgatis/rembg/blob/main/rembg/sessions/u2netp.py
- Model file: `u2netp.onnx`, 4,574,861 bytes
- SHA-256: `309c8469258dda742793dce0ebea8e6dd393174f89934733ecc8b14c76f4ddd8`
- License: [LICENSE.txt](LICENSE.txt)

The model estimates a 320 × 320 foreground mask. FileForge resizes that mask and applies it to the original image. A single distinct subject usually works best; fine hair, transparency and busy backgrounds may require further editing. User images are never sent to the model publisher or used for training.

The build script checks the checksum before packaging. If recreating the source checkout, save the weights at `app/models/u2netp.onnx` and retain this README and the Apache license beside them. These source files are included in the executable; model attribution and the license also appear in the generated release notices.
