# Build from this directory: the module has no other dependencies than go.mod.
FROM docker.io/golang:1.26-alpine AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY cmd ./cmd
COPY internal ./internal
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/gateway ./cmd/gateway

FROM docker.io/alpine:3.22
RUN adduser -D -H -u 10001 gateway
COPY --from=build /out/gateway /usr/local/bin/gateway
USER 10001
EXPOSE 8080
ENTRYPOINT ["/usr/local/bin/gateway"]
