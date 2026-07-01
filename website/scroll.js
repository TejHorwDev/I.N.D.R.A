document.addEventListener("DOMContentLoaded", () => {
    const observerOptions = {
        root: null,
        rootMargin: '0px',
        threshold: 0.15
    };

    const observer = new IntersectionObserver((entries, observer) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('is-visible');
                // Optional: stop observing once it has animated in
                // observer.unobserve(entry.target);
            }
        });
    }, observerOptions);

    const elementsToAnimate = document.querySelectorAll('.scroll-reveal, .scroll-fade, .scroll-scale, .scroll-slide-left, .scroll-slide-right');
    elementsToAnimate.forEach(el => {
        observer.observe(el);
    });
});
