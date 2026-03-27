# Times Series Compression

> Let's bechnark several strategies - that allows to represent large time series in a compact way, while still being able to reconstruct the original data with reasonable accuracy.

> We need to suport more than 1 million data points, and we want to be able to reconstruct the original data with an error of less than 1%.

Goals:

- We need to be able to compute statistis over temporal windows of various sizes.
- ...

Strategies:

- ...

Evaluation metrics:

- Compression ratio: the size of the compressed representation compared to the original data.
- Consistency: It's the (P95)- Based Metric latency from the original data - equal to the P95 - Based Metric latency from the reconstructed data.
- Computational efficiency: the time it takes to compress and decompress the data, as well as the time it takes to compute statistics
