FROM node:18-alpine
RUN npm install -g serve
WORKDIR /app
COPY out/ ./out/
EXPOSE 8080
CMD ["serve", "-s", "out", "-l", "8080"]
