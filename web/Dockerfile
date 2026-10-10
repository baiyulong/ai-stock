# Go 后端服务 - 需要 CGO（go-duckdb）
FROM golang:1.22-bookworm AS builder

WORKDIR /app

# 设置 Go 代理
ENV GO111MODULE=on \
    GOPROXY=https://goproxy.cn,direct \
    CGO_ENABLED=1 \
    GOOS=linux \
    GOARCH=amd64

# 安装 gcc（CGO 需要）
RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*

# 复制 Go 模块文件
COPY web/go.mod web/go.sum ./
RUN go mod download

# 复制源代码
COPY web/ .

# 编译
RUN go build -ldflags="-s -w" -o server .

# 运行阶段
FROM debian:bookworm-slim

# 安装运行时依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# 设置时区
ENV TZ=Asia/Shanghai

WORKDIR /app

# 复制二进制文件和静态文件
COPY --from=builder /app/server .
COPY web/static ./static

# 创建数据目录
RUN mkdir -p /app/data/database /app/data/duckdb

# 暴露端口
EXPOSE 18080

# 健康检查
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD apt-get update && apt-get install -y wget && wget --no-verbose --tries=1 --spider http://localhost:18080/api/health || exit 1

# 启动
CMD ["./server"]
