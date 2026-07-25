export class AppError extends Error {
  constructor(public readonly status: number, message: string, public readonly code = 'APP_ERROR') { super(message); }
}
