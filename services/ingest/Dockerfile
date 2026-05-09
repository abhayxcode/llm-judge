# syntax=docker/dockerfile:1.7
FROM golang:1.23-alpine AS builder
WORKDIR /src

COPY go.mod ./
RUN go mod download
COPY . .

ARG TARGETOS=linux
ARG TARGETARCH=amd64
RUN CGO_ENABLED=0 GOOS=${TARGETOS} GOARCH=${TARGETARCH} \
    go build -trimpath -ldflags="-s -w" -o /out/ingest ./cmd/ingest

FROM gcr.io/distroless/static:nonroot AS runtime
COPY --from=builder /out/ingest /ingest
EXPOSE 4318
USER nonroot:nonroot
ENTRYPOINT ["/ingest"]
