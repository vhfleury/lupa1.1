// Tipos globais do SvelteKit (sem App.Locals: o front é uma SPA estática).
declare global {
  namespace App {
    interface Error {
      message: string;
    }
  }
}

export {};
