import { PrismaClient } from "@/generated/prisma/client";
import { PrismaBetterSqlite3 } from "@prisma/adapter-better-sqlite3";
import bcrypt from "bcrypt";
import { categories, products } from "../src/data/products";

const url = process.env.DATABASE_URL;
if (!url) {
  throw new Error("DATABASE_URL no está definida.");
}

const adapter = new PrismaBetterSqlite3({ url });
const prisma = new PrismaClient({ adapter });

async function main() {
  console.log("🌱 Seeding database...");

  for (const cat of categories) {
    const { productCount: _, ...catData } = cat as { productCount?: number; slug: string; name: string; description: string; icon: string; color: string };
    void _;
    await prisma.category.upsert({
      where: { slug: catData.slug },
      update: catData,
      create: catData,
    });
  }
  console.log(`✓ ${categories.length} categories created`);

  for (const p of products) {
    await prisma.product.upsert({
      where: { id: p.id },
      update: {
        title: p.title,
        description: p.description,
        price: p.price,
        categorySlug: p.category,
        image: p.image,
        badge: p.badge ?? null,
        featured: p.featured ?? false,
        age: p.age,
        level: p.level,
        features: JSON.stringify(p.features ?? []),
        objectives: JSON.stringify(p.objectives ?? []),
      },
      create: {
        id: p.id,
        title: p.title,
        description: p.description,
        price: p.price,
        categorySlug: p.category,
        image: p.image,
        badge: p.badge ?? null,
        featured: p.featured ?? false,
        age: p.age,
        level: p.level,
        features: JSON.stringify(p.features ?? []),
        objectives: JSON.stringify(p.objectives ?? []),
      },
    });
  }
  console.log(`✓ ${products.length} products created`);

  const adminEmail = process.env.ADMIN_EMAIL?.toLowerCase() || "admin@paolapsicope.com";
  const adminPasswordRaw = process.env.ADMIN_PASSWORD || "admin123";
  const adminPassword = await bcrypt.hash(adminPasswordRaw, 12);
  await prisma.user.upsert({
    where: { email: adminEmail },
    update: {},
    create: {
      name: "Admin",
      email: adminEmail,
      password: adminPassword,
      isAdmin: true,
    },
  });
  console.log(`✓ admin user created (${adminEmail} / ${adminPasswordRaw})`);

  console.log("✅ Seed complete!");
}

main()
  .catch((e) => {
    console.error(e);
    process.exit(1);
  })
  .finally(() => prisma.$disconnect());
