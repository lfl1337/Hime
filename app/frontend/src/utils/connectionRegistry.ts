export interface Connection {
  id: string
  type: 'SSE' | 'WebSocket'
  url: string
  openedAt: Date
  eventCount: number
  bytesReceived: number
}

export const connectionRegistry = {
  connections: new Map<string, Connection>(),

  register(id: string, type: 'SSE' | 'WebSocket', url: string) {
    this.connections.set(id, {
      id,
      type,
      url,
      openedAt: new Date(),
      eventCount: 0,
      bytesReceived: 0,
    })
  },

  unregister(id: string) {
    this.connections.delete(id)
  },

  incrementEvents(id: string, bytes: number) {
    const conn = this.connections.get(id)
    if (conn) {
      conn.eventCount += 1
      conn.bytesReceived += bytes
    }
  },

  getAll(): Connection[] {
    return [...this.connections.values()]
  },
}
