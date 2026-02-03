import { plcSetupLabeler } from "@skyware/labeler/scripts";

async function run() {
    console.log("Generating key pair...");
    // This function usually handles PLC setup but we just want to see if it outputs keys
    // Since we are running it locally, we can catch the output.
    try {
        const result = await plcSetupLabeler({
            // Mocking some values just to get it to run the key generation part
            handle: "test.bsky.social",
            password: "test",
        });
        console.log("Result:", JSON.stringify(result, null, 2));
    } catch (e) {
        // It might fail on login but hopefully it generates/shows keys first or in error
        console.error("Caught error (this might contain keys if it started setup):", e);
    }
}

run();
