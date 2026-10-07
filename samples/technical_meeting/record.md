# Meeting record

## Summary

During the meeting the team reviewed recent model training and evaluation results, noting successful fine‑tuning of a BERT base model and an F1 score increase after gradient clipping. They addressed PCA issues by switching to SVD and discussed deployment plans including exporting to ONNX and serving with TensorRT. Decisions were made to retain cross‑entropy loss, log runs to weights and biases, and to proceed with the outlined deployment strategy. Action items include writing an A/B test plan by Thursday, profiling latency and exploring quantization, and exporting the model for deployment. The meeting concluded with a commitment to monitor latency and continue optimization.

## Minutes

### Training details

- Fine‑tuned BERT base on two A100 GPUs
- Used Adam optimizer with lr 3e-4 and cosine schedule
- Training successful

### PCA issue resolution

- Covariance matrix singular, eigen decomposition failed
- Switched to SVD in NumPy
- Top 50 PCs explain 90% variance

### Gradient clipping and metrics

- Checked L2 norm of gradients
- Gradient clipping fixed exploding gradients
- F1 score increased to 0.87

### Deployment plan

- Export model to ONNX
- Serve with TensorRT on GPU nodes in Kubernetes
- Latency 70ms at batch 32
- Plan to profile and try quantization

### Loss function decision

- Keep cross‑entropy loss
- Do not switch to focal loss

### A/B test plan

- Arjun to write A/B test plan by Thursday

### Logging

- Log every run to weights and biases

## Key decisions

1. Keep cross‑entropy loss and not switch to focal loss _(01:05: "We decided to keep the cross entropy loss and not switch to focal loss")_
2. Log every run to weights and biases _(01:18: "Let's also log every run to weights and biases")_

## Action items

| # | Task | Owner | Deadline | Source |
|---|------|-------|----------|--------|
| 1 | Export the model to ONNX and serve it with TensorRT on GPU nodes in Kubernetes cluster | Tom | Unspecified | 00:43 |
| 2 | Write up the A/B test plan by Thursday | Arjun | Thursday | 01:14 |
| 3 | Profile latency with insight and try and date quantization | Tom | Unspecified | 01:01 |
| 4 | Log every run to weights and biases | Unspecified | Unspecified | 01:18 |

## Open proposals and questions

_None recorded._
