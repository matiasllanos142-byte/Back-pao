export type CategorySlug =
  | "estimulacion"
  | "lectoescritura"
  | "dislexia"
  | "matematica"
  | "atencion-memoria"
  | "funciones-ejecutivas";

export type ProductLevel = "Inicial" | "Intermedio" | "Avanzado";

export interface User {
  id: string;
  name: string;
  email: string;
  isAdmin: boolean;
  createdAt: string;
}

export interface Category {
  slug: CategorySlug;
  name: string;
  description: string;
  icon: string;
  color: string;
  productCount: number;
}

export interface Product {
  id: string;
  title: string;
  description: string;
  price: number;
  category: CategorySlug;
  image: string;
  badge?: string;
  featured: boolean;
  age: string;
  level: ProductLevel;
  features: string[];
  objectives: string[];
}

export type OrderStatus = "completada" | "pendiente" | "fallida" | "reembolsada";

export interface Order {
  id: string;
  items: { product: Product; quantity: number }[];
  total: number;
  status: OrderStatus;
  createdAt: string;
  customer: {
    name: string;
    email: string;
  };
}
