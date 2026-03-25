FROM node:20-bookworm-slim

WORKDIR /app
COPY package.json package.json
RUN npm install
COPY . .
RUN npm run build
ENV PORT=3000
CMD ["npm", "start"]
