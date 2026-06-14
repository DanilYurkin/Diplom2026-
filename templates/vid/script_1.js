document.addEventListener("DOMContentLoaded", function() {
    console.log("Сайт OMB загружен");

    document.querySelector("a[href='id.html']").addEventListener("click", function(event) {
        event.preventDefault();
        location.reload();
    });

    document.querySelector("a[href='btc.html']").addEventListener("click", function(event) {
        event.preventDefault();
        openPage("Продажа BTC");
    });

    document.querySelector("a[href='btb.html']").addEventListener("click", function(event) {
        event.preventDefault();
        openPage("Продажа BTB");
    });

    document.querySelector("a[href='cart.html']").addEventListener("click", function(event) {
        event.preventDefault();
        openPage("Корзина");
    });

    document.querySelector("a[href='account.html']").addEventListener("click", function(event) {
        event.preventDefault();
        openPage("Личный кабинет");
    });

    function openPage(title) {
        const main = document.querySelector("main");
        main.innerHTML = `<h2>${title}</h2><p>Страница в разработке...</p>`;
    }
});
