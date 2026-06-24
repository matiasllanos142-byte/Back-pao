import Link from "next/link";
import Container from "@/components/ui/Container";
import Button from "@/components/ui/Button";

export default function NotFound() {
  return (
    <section className="flex flex-1 items-center justify-center py-20">
      <Container>
        <div className="flex flex-col items-center text-center gap-6">
          <span className="text-7xl font-bold text-primary/20">404</span>
          <h1 className="text-2xl font-bold text-text">
            Página no encontrada
          </h1>
          <p className="text-text-muted max-w-md">
            Lo sentimos, la página que buscas no existe o fue movida a otra ubicación.
          </p>
          <Link href="/">
            <Button>Volver al inicio</Button>
          </Link>
        </div>
      </Container>
    </section>
  );
}
