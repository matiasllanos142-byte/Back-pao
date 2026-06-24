import type { CategorySlug } from "@/types";

export interface LibraryItem {
  id: string;
  productId: string;
  title: string;
  category: CategorySlug;
  downloadedAt: string;
  format: "pdf";
  size: string;
}

export interface LibraryCollection {
  id: string;
  name: string;
  description: string;
  itemCount: number;
  updatedAt: string;
}

export const MOCK_LIBRARY: LibraryItem[] = [];

export const MOCK_COLLECTIONS: LibraryCollection[] = [
  {
    id: "recientes",
    name: "Descargas recientes",
    description: "Los últimos recursos que descargaste.",
    itemCount: 0,
    updatedAt: new Date().toISOString(),
  },
  {
    id: "favoritos",
    name: "Favoritos",
    description: "Recursos que guardaste para después.",
    itemCount: 0,
    updatedAt: new Date().toISOString(),
  },
];
